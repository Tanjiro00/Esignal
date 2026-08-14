"""Build per-channel feeds and check that personalization actually happened.

The decisive test is at the bottom: feeds for different channels must differ.
If several channels get the same list, the product is a generic newsletter and
there is nothing to sell.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from es_core import channel_profile
from es_core.anchors import AnchorPolicy, BackgroundCorpus
from es_core.demand_items import DemandPolicy, attach_answers, build_items
from es_core.feed import build_feed, overlap, overlap_vs_chance
from es_core.verification import apply as apply_verifications
from es_core.verification import parse_response
from es_eval import dataset as dataset_module
from scripts.build_demand_items import load_comments


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--as-of", type=_date, required=True)
    parser.add_argument("--window", type=int, default=45)
    parser.add_argument("--channels", type=int, default=3)
    parser.add_argument("--show", type=int, default=5)
    parser.add_argument("--verifications", type=Path)
    args = parser.parse_args()

    comments, comment_embeddings = load_comments(args.data / "comments.jsonl")
    data = dataset_module.load(
        cohort=args.data / "cohort.jsonl.gz",
        embeddings=args.data / "embeddings-v1.jsonl",
        discovery=args.data / "discovery.csv",
    )
    video_meta = {v.video_id: (v.title, v.published_at) for v in data.videos}

    policy = DemandPolicy(window_days=args.window)
    items = build_items(comments, comment_embeddings, as_of=args.as_of, policy=policy)
    items = attach_answers(items, data.embeddings, video_meta, as_of=args.as_of, policy=policy)
    if args.verifications:
        import json as _json

        raw = {
            _json.loads(line)["item_id"]: _json.loads(line)["raw"]
            for line in args.verifications.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        by_id = {item.item_id: item for item in items}
        verdicts = [parse_response(by_id[key], value) for key, value in raw.items() if key in by_id]
        before = len(items)
        items = apply_verifications(items, verdicts)
        print(f"demand items={before} -> verified={len(items)}")
    else:
        print(f"demand items={len(items)}")

    corpus = BackgroundCorpus.build(
        data.videos, as_of=args.as_of, policy=AnchorPolicy(background_days=365)
    )

    # Pick the channels with the most embedded uploads — those have real profiles.
    embedded_per_channel = Counter(
        video.channel_id for video in data.videos if video.video_id in data.embeddings
    )
    candidates = [channel for channel, _ in embedded_per_channel.most_common(40)]

    profiles = []
    for channel in candidates:
        profile = channel_profile.build(
            channel, data.videos, data.embeddings, as_of=args.as_of, corpus=corpus
        )
        if profile is not None:
            profiles.append(profile)
    print(f"profiles built={len(profiles)}\n")

    feeds = {}
    for profile in profiles[: args.channels]:
        feed = build_feed(profile, items, data.embeddings, as_of=args.as_of)
        feeds[profile.channel_id] = feed
        title = video_meta.get(profile.recent_video_ids[0], ("", None))[0]
        print(f"=== {profile.channel_id} ({profile.video_count} videos, r={profile.radius:.2f})")
        print(f"    subject: {profile.subject or '-'}")
        print(f"    latest : {title[:70]}")
        actionable = [entry for entry in feed if entry.actionable]
        print(f"    feed   : {len(feed)} items, {len(actionable)} actionable")
        for entry in actionable[: args.show]:
            print(
                f"      fit={entry.fit:.2f} vol={entry.volume:5.1f} "
                f"askers={entry.item.distinct_askers:2d} | {entry.item.headline[:78]}"
            )
        print()

    keys = list(feeds)
    print(f"--- personalization check (pool={len(items)}, 1.00x = no better than chance) ---")
    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            share = overlap(feeds[left], feeds[right])
            ratio = overlap_vs_chance(feeds[left], feeds[right], pool_size=len(items))
            print(
                f"  {left[:12]} vs {right[:12]}: overlap {share * 100:3.0f}% = {ratio:.2f}x chance"
            )


if __name__ == "__main__":
    main()
