"""Build the demand feed from stored comments.

Runs the same code the product will run. With `--calibrate` it instead reports
the similarity distribution between question clusters and videos, which is how
the answer threshold is chosen from data rather than guessed.
"""

from __future__ import annotations

import argparse
import base64
import json
import struct
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from es_core.demand_items import (
    DemandComment,
    DemandPolicy,
    attach_answers,
    build_items,
)
from es_eval import dataset as dataset_module


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def load_comments(path: Path) -> tuple[list[DemandComment], dict[str, tuple[float, ...]]]:
    comments: list[DemandComment] = []
    embeddings: dict[str, tuple[float, ...]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            comment_id = str(row["comment_id"])
            dimensions = int(row["dimensions"])
            raw = base64.b64decode(str(row["embedding_base64"]))
            embeddings[comment_id] = struct.unpack(f"<{dimensions}f", raw)
            comments.append(
                DemandComment(
                    comment_id=comment_id,
                    video_id=str(row["video_id"]),
                    channel_id=str(row["channel_id"]),
                    text=str(row["text"]),
                    published_at=datetime.fromisoformat(
                        str(row["published_at"]).replace("Z", "+00:00")
                    ),
                    like_count=int(row.get("like_count") or 0),
                    taxonomy=str(row.get("taxonomy") or ""),
                    author_hash=str(row.get("author_hash") or ""),
                )
            )
    return comments, embeddings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--as-of", type=_date, required=True)
    parser.add_argument("--window", type=int, default=30)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--calibrate", action="store_true")
    args = parser.parse_args()

    comments, comment_embeddings = load_comments(args.data / "comments.jsonl")
    data = dataset_module.load(
        cohort=args.data / "cohort.jsonl.gz",
        embeddings=args.data / "embeddings-v1.jsonl",
        discovery=args.data / "discovery.csv",
    )
    video_meta = {video.video_id: (video.title, video.published_at) for video in data.videos}
    print(
        f"comments={len(comments)} videos={len(data.videos)} "
        f"video_embeddings={len(data.embeddings)}"
    )

    policy = DemandPolicy(window_days=args.window)
    items = build_items(comments, comment_embeddings, as_of=args.as_of, policy=policy)
    print(f"demand items={len(items)}")
    if not items:
        return

    if args.calibrate:
        _calibrate(items, data, video_meta)
        return

    items = attach_answers(
        items,
        data.embeddings,
        video_meta,
        as_of=args.as_of,
        policy=policy,
    )
    unanswered = [item for item in items if not item.answered]
    print(f"unanswered={len(unanswered)} answered={len(items) - len(unanswered)}\n")

    for item in sorted(unanswered, key=lambda entry: -entry.volume_score)[: args.limit]:
        print(
            f"[{item.volume_score:6.2f}] {item.distinct_askers} askers / "
            f"{item.distinct_channels} channels / {item.total_likes} likes / "
            f"{item.age_days(args.as_of):.0f}d ago"
        )
        print(f"    Q: {item.question[:150]}")
        for comment in item.comments[1:3]:
            print(f"       + {comment.text.strip()[:110]}")
        print(f"       https://www.youtube.com/watch?v={item.comments[0].video_id}")


def _calibrate(items: tuple, data: object, video_meta: dict) -> None:
    """Report how close questions sit to their carrier videos and to others."""

    embeddings = data.embeddings  # type: ignore[attr-defined]
    ids = [v for v in embeddings if v in video_meta]
    matrix = np.stack([np.asarray(embeddings[v], dtype=np.float32) for v in ids])
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    carrier_scores: list[float] = []
    other_scores: list[float] = []
    for item in items:
        centroid = np.asarray(item.centroid, dtype=np.float32)
        similarity = matrix @ centroid
        carriers = {comment.video_id for comment in item.comments}
        for index, video_id in enumerate(ids):
            (carrier_scores if video_id in carriers else other_scores).append(
                float(similarity[index])
            )
    for name, values in (("carrier videos", carrier_scores), ("other videos", other_scores)):
        array = np.asarray(values)
        if not array.size:
            continue
        print(
            f"{name:16} n={array.size:8d} "
            f"p50={np.percentile(array, 50):.3f} p90={np.percentile(array, 90):.3f} "
            f"p99={np.percentile(array, 99):.3f} max={array.max():.3f}"
        )


if __name__ == "__main__":
    main()
