"""Cross-source matching in one semantic space.

Term matching failed as a join: "ecc" retrieves ECC memory threads and "26b"
retrieves comments about model sizes. Words are the wrong key.

Both sides are embedded with the same model, so the join can be semantic
instead. An upstream item belongs to a topic when its vector is close to the
topic centroid — which is how "ECC (Claude Code Agent OS)" separates from "ZFS
scrubs with no ECC" without anyone writing a rule about it.

The question measured here: for topics the core surfaces, did matching upstream
discussion exist *before* the first video?
"""

from __future__ import annotations

import argparse
import base64
import json
import struct
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from es_core.identity import TopicRegistry
from es_core.pipeline import build_candidates
from es_eval import dataset as dataset_module


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def load_upstream(path: Path) -> tuple[list[dict[str, object]], np.ndarray]:
    items: list[dict[str, object]] = []
    vectors: list[np.ndarray] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            dimensions = int(row["dimensions"])
            raw = base64.b64decode(str(row["embedding_base64"]))
            vector = np.asarray(struct.unpack(f"<{dimensions}f", raw), dtype=np.float32)
            norm = float(np.linalg.norm(vector))
            items.append(
                {
                    "title": row["title"],
                    "at": datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")),
                    "points": row.get("points") or 0,
                    "url": row.get("url") or "",
                }
            )
            vectors.append(vector / norm if norm else vector)
    return items, np.stack(vectors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--checkpoint", type=_date, required=True)
    parser.add_argument("--threshold", type=float, default=0.62)
    parser.add_argument("--show", type=int, default=20)
    args = parser.parse_args()

    data = dataset_module.load(
        cohort=args.data / "cohort.jsonl.gz",
        embeddings=args.data / "embeddings-v1.jsonl",
        discovery=args.data / "discovery.csv",
    )
    items, matrix = load_upstream(args.data / "upstream_hn.jsonl")
    by_id = {video.video_id: video for video in data.videos}
    print(f"upstream_items={len(items)} threshold={args.threshold}")

    candidates = build_candidates(
        data.videos,
        data.embeddings,
        as_of=args.checkpoint,
        registry=TopicRegistry(),
    )
    publishable = [
        candidate
        for candidate in candidates
        if candidate.evidence.status == "accepted" and candidate.anchors
    ]
    publishable.sort(key=lambda candidate: -max(anchor.score for anchor in candidate.anchors))

    leads: list[float] = []
    matched = 0
    ahead = 0
    shown = 0
    for candidate in publishable:
        vectors = [
            data.embeddings[video_id]
            for video_id in candidate.member_video_ids
            if video_id in data.embeddings
        ]
        members = [by_id[vid] for vid in candidate.member_video_ids if vid in by_id]
        if not vectors or not members:
            continue
        centroid = np.asarray(vectors, dtype=np.float32).mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        if not norm:
            continue
        centroid = centroid / norm

        similarity = matrix @ centroid
        hits = np.flatnonzero(similarity >= args.threshold)
        if hits.size == 0:
            continue
        matched += 1
        youtube_first = min(video.published_at for video in members)
        before = [
            (float(similarity[index]), items[index])
            for index in hits.tolist()
            if items[index]["at"] < youtube_first
        ]
        if not before:
            continue
        ahead += 1
        best = max(before, key=lambda pair: pair[0])
        earliest = min(before, key=lambda pair: pair[1]["at"])
        lead = (youtube_first - earliest[1]["at"]).total_seconds() / 86_400
        leads.append(lead)
        if shown < args.show:
            shown += 1
            print(
                f"\n{candidate.anchors[0].term!r} — first video {youtube_first.date()}, "
                f"lead {lead:.1f}d over {len(before)} upstream items"
            )
            print(f"   video    : {members[0].title[:76]}")
            print(
                f"   upstream : [{best[0]:.2f}] {best[1]['at'].date()} {str(best[1]['title'])[:70]}"
            )

    leads.sort()
    median = leads[len(leads) // 2] if leads else 0.0
    print(
        f"\ntopics={len(publishable)} with_upstream_match={matched} "
        f"upstream_first={ahead} median_lead_days={median:.1f}"
    )
    if leads:
        share = sum(1 for value in leads if value >= 7) / len(leads)
        print(f"share with lead >= 7 days: {share * 100:.0f}%")


if __name__ == "__main__":
    main()
