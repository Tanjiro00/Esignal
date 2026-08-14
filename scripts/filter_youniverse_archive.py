from __future__ import annotations

import argparse
import csv
import gzip
import importlib
import json
import os
from collections import Counter
from collections.abc import Iterable
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, TextIO, cast

from packages.backtest.youniverse import (
    detect_historical_ai_anchor,
    parse_youniverse_payload,
)

try:  # Optional evaluation-only accelerator; stdlib remains the tested fallback.
    _orjson: ModuleType | None = importlib.import_module("orjson")
except ImportError:  # pragma: no cover - exercised when the optional wheel exists.
    _orjson = None

TRAIN_AI_START = datetime(2015, 7, 1, tzinfo=UTC)
TRAIN_END = datetime(2018, 12, 30, 23, 59, 59, tzinfo=UTC)
HOLDOUT_AI_START = datetime(2018, 7, 1, tzinfo=UTC)
HOLDOUT_END = datetime(2019, 10, 20, 23, 59, 59, tzinfo=UTC)
TRAIN_BASELINE_START = datetime(2015, 1, 1, tzinfo=UTC)
HOLDOUT_BASELINE_START = datetime(2018, 1, 1, tzinfo=UTC)
_CHANNEL_PREFIX = '"channel_id": "'


def _json_loads(line: str) -> dict[str, Any]:
    if _orjson is not None:
        return cast(dict[str, Any], _orjson.loads(line))
    return cast(dict[str, Any], json.loads(line))


def _json_dumps(payload: dict[str, Any]) -> str:
    if _orjson is not None:
        return cast(bytes, _orjson.dumps(payload)).decode()
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _channel_id_without_deserializing(line: str) -> str | None:
    """Read the canonical YouNiverse channel field before full JSON parsing.

    The released archive uses one JSON object per line with the exact serialized
    field prefix below. A conservative JSON fallback handles synthetic rows or a
    future archive serialization without changing admission semantics.
    """

    start = line.find(_CHANNEL_PREFIX)
    if start >= 0:
        value_start = start + len(_CHANNEL_PREFIX)
        value_end = line.find('"', value_start)
        if value_end >= value_start:
            return line[value_start:value_end]
    try:
        return str(_json_loads(line).get("channel_id") or "").strip()
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _atomic_gzip_text(path: Path, stack: ExitStack) -> tuple[Path, TextIO]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    handle = stack.enter_context(
        gzip.open(  # noqa: SIM115 - the ExitStack owns this handle.
            temporary, "wt", encoding="utf-8", newline=""
        )
    )
    return temporary, handle


def _finish_atomic(temporary: Path, destination: Path) -> None:
    os.replace(temporary, destination)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _write_channels(path: Path, channels: set[str]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text("\n".join(sorted(channels)) + "\n")
    os.replace(temporary, path)


def filter_ai_metadata(
    lines: Iterable[str],
    *,
    train_output: TextIO,
    holdout_output: TextIO,
) -> tuple[dict[str, Any], set[str], set[str]]:
    total = 0
    invalid = 0
    accepted = 0
    train_count = 0
    holdout_count = 0
    anchors: Counter[str] = Counter()
    years: Counter[int] = Counter()
    categories: Counter[str] = Counter()
    train_channels: set[str] = set()
    holdout_channels: set[str] = set()
    for line in lines:
        total += 1
        try:
            payload = _json_loads(line)
        except (ValueError, TypeError, json.JSONDecodeError):
            invalid += 1
            continue
        title = str(payload.get("title") or "")
        anchor = detect_historical_ai_anchor(title)
        if not anchor:
            continue
        try:
            video = parse_youniverse_payload(payload)
        except (ValueError, TypeError):
            invalid += 1
            continue
        if not video.video_id or not video.channel_id:
            continue
        accepted += 1
        anchors[anchor] += 1
        years[video.upload_date.year] += 1
        categories[video.category or "unknown"] += 1
        serialized = _json_dumps(video.json_payload())
        if TRAIN_AI_START <= video.upload_date <= TRAIN_END:
            train_output.write(serialized + "\n")
            train_count += 1
            train_channels.add(video.channel_id)
        if HOLDOUT_AI_START <= video.upload_date <= HOLDOUT_END:
            holdout_output.write(serialized + "\n")
            holdout_count += 1
            holdout_channels.add(video.channel_id)
    stats: dict[str, Any] = {
        "total_records": total,
        "invalid_records": invalid,
        "accepted_ai_records_all_dates": accepted,
        "train_records": train_count,
        "holdout_records_sealed": holdout_count,
        "train_channels": len(train_channels),
        "holdout_channels_sealed": len(holdout_channels),
        "anchors_all_dates": dict(sorted(anchors.items())),
        "years_all_dates": {str(key): value for key, value in sorted(years.items())},
        "categories_all_dates": dict(categories.most_common()),
    }
    return stats, train_channels, holdout_channels


def filter_channel_baselines(
    lines: Iterable[str],
    *,
    train_channels: set[str],
    holdout_channels: set[str],
    train_output: TextIO,
    holdout_output: TextIO,
) -> dict[str, int]:
    total = 0
    invalid = 0
    train_count = 0
    holdout_count = 0
    relevant_channels = train_channels | holdout_channels
    for line in lines:
        total += 1
        channel_id = _channel_id_without_deserializing(line)
        if channel_id is None:
            invalid += 1
            continue
        if channel_id not in relevant_channels:
            continue
        try:
            payload = _json_loads(line)
        except (ValueError, TypeError, json.JSONDecodeError):
            invalid += 1
            continue
        try:
            video = parse_youniverse_payload(payload)
        except (ValueError, TypeError):
            invalid += 1
            continue
        payload = {
            "video_id": video.video_id,
            "channel_id": video.channel_id,
            "upload_date": video.upload_date.isoformat(),
            "crawl_date": video.crawl_date.isoformat(),
            "final_view_count": video.final_view_count,
        }
        serialized = _json_dumps(payload)
        if (
            video.channel_id in train_channels
            and TRAIN_BASELINE_START <= video.upload_date <= TRAIN_END
        ):
            train_output.write(serialized + "\n")
            train_count += 1
        if (
            video.channel_id in holdout_channels
            and HOLDOUT_BASELINE_START <= video.upload_date <= HOLDOUT_END
        ):
            holdout_output.write(serialized + "\n")
            holdout_count += 1
    return {
        "total_records": total,
        "invalid_records": invalid,
        "train_baseline_records": train_count,
        "holdout_baseline_records_sealed": holdout_count,
    }


def filter_grouped_metadata(
    lines: Iterable[str],
    *,
    train_ai_output: TextIO,
    holdout_ai_output: TextIO,
    train_baseline_output: TextIO,
    holdout_baseline_output: TextIO,
) -> tuple[dict[str, Any], set[str], set[str]]:
    """Filter AI videos and their channel baselines in one channel-grouped pass.

    YouNiverse stores each channel as one contiguous run. The function verifies
    that invariant and fails instead of silently dropping earlier baseline rows
    if a completed channel ever reappears.
    """

    total = 0
    invalid = 0
    accepted = 0
    train_count = 0
    holdout_count = 0
    train_baseline_count = 0
    holdout_baseline_count = 0
    anchors: Counter[str] = Counter()
    years: Counter[int] = Counter()
    categories: Counter[str] = Counter()
    train_channels: set[str] = set()
    holdout_channels: set[str] = set()
    completed_channels: set[str] = set()
    current_channel: str | None = None
    current_payloads: list[dict[str, Any]] = []

    def flush_channel(channel_id: str, payloads: list[dict[str, Any]]) -> None:
        nonlocal accepted
        nonlocal invalid
        nonlocal train_count
        nonlocal holdout_count
        nonlocal train_baseline_count
        nonlocal holdout_baseline_count
        ai_rows: list[tuple[Any, str]] = []
        for payload in payloads:
            anchor = detect_historical_ai_anchor(str(payload.get("title") or ""))
            if not anchor:
                continue
            try:
                video = parse_youniverse_payload(payload)
            except (ValueError, TypeError):
                invalid += 1
                continue
            if not video.video_id:
                continue
            accepted += 1
            anchors[anchor] += 1
            years[video.upload_date.year] += 1
            categories[video.category or "unknown"] += 1
            ai_rows.append((video, anchor))
        train_ai = [
            video for video, _ in ai_rows if TRAIN_AI_START <= video.upload_date <= TRAIN_END
        ]
        holdout_ai = [
            video for video, _ in ai_rows if HOLDOUT_AI_START <= video.upload_date <= HOLDOUT_END
        ]
        if not train_ai and not holdout_ai:
            return
        for video in train_ai:
            train_ai_output.write(_json_dumps(video.json_payload()) + "\n")
            train_count += 1
        for video in holdout_ai:
            holdout_ai_output.write(_json_dumps(video.json_payload()) + "\n")
            holdout_count += 1
        if train_ai:
            train_channels.add(channel_id)
        if holdout_ai:
            holdout_channels.add(channel_id)
        for payload in payloads:
            try:
                video = parse_youniverse_payload(payload)
            except (ValueError, TypeError):
                invalid += 1
                continue
            baseline_payload = {
                "video_id": video.video_id,
                "channel_id": video.channel_id,
                "upload_date": video.upload_date.isoformat(),
                "crawl_date": video.crawl_date.isoformat(),
                "final_view_count": video.final_view_count,
            }
            serialized = _json_dumps(baseline_payload)
            if train_ai and TRAIN_BASELINE_START <= video.upload_date <= TRAIN_END:
                train_baseline_output.write(serialized + "\n")
                train_baseline_count += 1
            if holdout_ai and HOLDOUT_BASELINE_START <= video.upload_date <= HOLDOUT_END:
                holdout_baseline_output.write(serialized + "\n")
                holdout_baseline_count += 1

    for line in lines:
        total += 1
        try:
            payload = _json_loads(line)
        except (ValueError, TypeError, json.JSONDecodeError):
            invalid += 1
            continue
        channel_id = str(payload.get("channel_id") or "").strip()
        if not channel_id:
            invalid += 1
            continue
        if current_channel is None:
            current_channel = channel_id
        if channel_id != current_channel:
            flush_channel(current_channel, current_payloads)
            completed_channels.add(current_channel)
            if channel_id in completed_channels:
                raise ValueError(f"YouNiverse channel rows are not contiguous: {channel_id}")
            current_channel = channel_id
            current_payloads = []
        current_payloads.append(payload)
    if current_channel is not None:
        flush_channel(current_channel, current_payloads)

    stats: dict[str, Any] = {
        "total_records": total,
        "invalid_records": invalid,
        "accepted_ai_records_all_dates": accepted,
        "train_records": train_count,
        "holdout_records_sealed": holdout_count,
        "train_baseline_records": train_baseline_count,
        "holdout_baseline_records_sealed": holdout_baseline_count,
        "train_channels": len(train_channels),
        "holdout_channels_sealed": len(holdout_channels),
        "channel_runs": len(completed_channels) + (1 if current_channel else 0),
        "anchors_all_dates": dict(sorted(anchors.items())),
        "years_all_dates": {str(key): value for key, value in sorted(years.items())},
        "categories_all_dates": dict(categories.most_common()),
    }
    return stats, train_channels, holdout_channels


def filter_channel_table(
    lines: Iterable[str],
    *,
    train_channels: set[str],
    holdout_channels: set[str],
    train_output: TextIO,
    holdout_output: TextIO,
) -> dict[str, int]:
    iterator = iter(lines)
    try:
        header = next(iterator)
    except StopIteration as error:
        raise ValueError("YouNiverse channel table is empty") from error
    fieldnames = next(csv.reader([header], delimiter="\t"))
    if "channel" not in fieldnames:
        raise ValueError("YouNiverse channel table is missing the channel column")
    channel_index = fieldnames.index("channel")
    canonical_header = header if header.endswith(("\n", "\r")) else f"{header}\n"
    train_output.write(canonical_header)
    holdout_output.write(canonical_header)
    train_count = 0
    holdout_count = 0
    for line in iterator:
        fields = line.split("\t", channel_index + 1)
        if len(fields) <= channel_index:
            continue
        channel = fields[channel_index].strip('"')
        if channel in train_channels:
            train_output.write(line)
            train_count += 1
        if channel in holdout_channels:
            holdout_output.write(line)
            holdout_count += 1
    return {"train_channel_rows": train_count, "holdout_channel_rows_sealed": holdout_count}


def _read_channels(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def _filter_ai_command(args: argparse.Namespace) -> None:
    outputs = (args.train_output, args.holdout_output)
    with ExitStack() as stack:
        source = stack.enter_context(gzip.open(args.source, "rt", encoding="utf-8"))
        train_temp, train = _atomic_gzip_text(args.train_output, stack)
        holdout_temp, holdout = _atomic_gzip_text(args.holdout_output, stack)
        stats, train_channels, holdout_channels = filter_ai_metadata(
            source,
            train_output=train,
            holdout_output=holdout,
        )
    for temporary, output in zip((train_temp, holdout_temp), outputs, strict=True):
        _finish_atomic(temporary, output)
    _write_channels(args.train_channels, train_channels)
    _write_channels(args.holdout_channels, holdout_channels)
    _write_json_atomic(args.stats_output, stats)


def _filter_baselines_command(args: argparse.Namespace) -> None:
    train_channels = _read_channels(args.train_channels)
    holdout_channels = _read_channels(args.holdout_channels)
    outputs = (args.train_output, args.holdout_output)
    with ExitStack() as stack:
        source = stack.enter_context(gzip.open(args.source, "rt", encoding="utf-8"))
        train_temp, train = _atomic_gzip_text(args.train_output, stack)
        holdout_temp, holdout = _atomic_gzip_text(args.holdout_output, stack)
        stats = filter_channel_baselines(
            source,
            train_channels=train_channels,
            holdout_channels=holdout_channels,
            train_output=train,
            holdout_output=holdout,
        )
    for temporary, output in zip((train_temp, holdout_temp), outputs, strict=True):
        _finish_atomic(temporary, output)
    _write_json_atomic(args.stats_output, stats)


def _filter_grouped_command(args: argparse.Namespace) -> None:
    outputs = (
        args.train_ai_output,
        args.holdout_ai_output,
        args.train_baseline_output,
        args.holdout_baseline_output,
    )
    with ExitStack() as stack:
        source = stack.enter_context(gzip.open(args.source, "rt", encoding="utf-8"))
        train_ai_temp, train_ai = _atomic_gzip_text(args.train_ai_output, stack)
        holdout_ai_temp, holdout_ai = _atomic_gzip_text(args.holdout_ai_output, stack)
        train_baseline_temp, train_baseline = _atomic_gzip_text(args.train_baseline_output, stack)
        holdout_baseline_temp, holdout_baseline = _atomic_gzip_text(
            args.holdout_baseline_output, stack
        )
        stats, train_channels, holdout_channels = filter_grouped_metadata(
            source,
            train_ai_output=train_ai,
            holdout_ai_output=holdout_ai,
            train_baseline_output=train_baseline,
            holdout_baseline_output=holdout_baseline,
        )
    temporary_outputs = (
        train_ai_temp,
        holdout_ai_temp,
        train_baseline_temp,
        holdout_baseline_temp,
    )
    for temporary, output in zip(temporary_outputs, outputs, strict=True):
        _finish_atomic(temporary, output)
    _write_channels(args.train_channels, train_channels)
    _write_channels(args.holdout_channels, holdout_channels)
    _write_json_atomic(args.stats_output, stats)


def _filter_table_command(args: argparse.Namespace) -> None:
    train_channels = _read_channels(args.train_channels)
    holdout_channels = _read_channels(args.holdout_channels)
    outputs = (args.train_output, args.holdout_output)
    with ExitStack() as stack:
        source = stack.enter_context(gzip.open(args.source, "rt", encoding="utf-8", newline=""))
        train_temp, train = _atomic_gzip_text(args.train_output, stack)
        holdout_temp, holdout = _atomic_gzip_text(args.holdout_output, stack)
        stats = filter_channel_table(
            source,
            train_channels=train_channels,
            holdout_channels=holdout_channels,
            train_output=train,
            holdout_output=holdout,
        )
    for temporary, output in zip((train_temp, holdout_temp), outputs, strict=True):
        _finish_atomic(temporary, output)
    _write_json_atomic(args.stats_output, stats)


def _common_outputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--train-output", required=True, type=Path)
    parser.add_argument("--holdout-output", required=True, type=Path)
    parser.add_argument("--stats-output", required=True, type=Path)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    ai_parser = subparsers.add_parser("filter-ai")
    _common_outputs(ai_parser)
    ai_parser.add_argument("--train-channels", required=True, type=Path)
    ai_parser.add_argument("--holdout-channels", required=True, type=Path)
    ai_parser.set_defaults(handler=_filter_ai_command)

    baseline_parser = subparsers.add_parser("filter-baselines")
    _common_outputs(baseline_parser)
    baseline_parser.add_argument("--train-channels", required=True, type=Path)
    baseline_parser.add_argument("--holdout-channels", required=True, type=Path)
    baseline_parser.set_defaults(handler=_filter_baselines_command)

    grouped_parser = subparsers.add_parser("filter-grouped")
    grouped_parser.add_argument("--source", required=True, type=Path)
    grouped_parser.add_argument("--train-ai-output", required=True, type=Path)
    grouped_parser.add_argument("--holdout-ai-output", required=True, type=Path)
    grouped_parser.add_argument("--train-baseline-output", required=True, type=Path)
    grouped_parser.add_argument("--holdout-baseline-output", required=True, type=Path)
    grouped_parser.add_argument("--train-channels", required=True, type=Path)
    grouped_parser.add_argument("--holdout-channels", required=True, type=Path)
    grouped_parser.add_argument("--stats-output", required=True, type=Path)
    grouped_parser.set_defaults(handler=_filter_grouped_command)

    table_parser = subparsers.add_parser("filter-channel-table")
    _common_outputs(table_parser)
    table_parser.add_argument("--train-channels", required=True, type=Path)
    table_parser.add_argument("--holdout-channels", required=True, type=Path)
    table_parser.set_defaults(handler=_filter_table_command)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
