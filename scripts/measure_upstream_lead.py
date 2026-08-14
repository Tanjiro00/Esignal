"""Does the signal arrive upstream before it arrives on YouTube?

For every anchor term the v2 core extracted at a checkpoint, this compares the
first YouTube upload in the cluster with dated evidence from Hacker News and
GitHub.

The comparison is deliberately not "first mention ever" — a generic phrase has
been said on Hacker News for a decade. It measures a *burst*: how much upstream
activity appeared in the 30 days before the first video, against the same term's
baseline rate a year earlier. A term that spikes upstream first is a term we
could have seen coming.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

from es_core.entity import EntityEvidence, resolve
from es_core.identity import TopicRegistry
from es_core.pipeline import build_candidates
from es_eval import dataset as dataset_module
from es_ingest.upstream.base import HttpCache, UpstreamMention
from es_ingest.upstream.github import GitHubSource
from es_ingest.upstream.hackernews import HackerNewsSource

PRE_WINDOW_DAYS = 30
BASELINE_OFFSET_DAYS = 365


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _count(mentions: tuple[UpstreamMention, ...], start: datetime, end: datetime) -> float:
    return sum(mention.weight for mention in mentions if start <= mention.at < end)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--checkpoint", type=_date, required=True)
    parser.add_argument("--terms", type=int, default=40)
    args = parser.parse_args()

    data = dataset_module.load(
        cohort=args.data / "cohort.jsonl.gz",
        embeddings=args.data / "embeddings-v1.jsonl",
        discovery=args.data / "discovery.csv",
    )
    candidates = build_candidates(
        data.videos,
        data.embeddings,
        as_of=args.checkpoint,
        registry=TopicRegistry(),
    )
    by_id = {video.video_id: video for video in data.videos}
    publishable = [
        candidate
        for candidate in candidates
        if candidate.evidence.status == "accepted" and candidate.anchors
    ]
    publishable.sort(key=lambda candidate: -max(anchor.score for anchor in candidate.anchors))

    hacker_news = HackerNewsSource(HttpCache(args.cache / "hn"))
    github = GitHubSource(HttpCache(args.cache / "gh", min_interval_seconds=6.5))

    print(f"candidates={len(candidates)} publishable={len(publishable)} probing={args.terms}\n")
    print(f"{'anchor':22} {'yt first':>10} {'pre30':>7} {'base':>7} {'lead d':>7}  first upstream")

    leads: list[float] = []
    bursty = 0
    confirmed = 0
    corroborated = 0
    probed = 0
    seen: set[str] = set()
    for candidate in publishable:
        term = candidate.anchors[0].term
        if term in seen:
            continue
        seen.add(term)
        members = [by_id[vid] for vid in candidate.member_video_ids if vid in by_id]
        if not members:
            continue
        youtube_first = min(video.published_at for video in members)

        raw = hacker_news.mentions(term) + github.mentions(term)
        entity = resolve(
            term,
            [EntityEvidence(m.source, m.at, m.weight, m.position, m.title, m.url) for m in raw],
        )
        # Only structurally named evidence counts; incidental text mentions are
        # kept in the entity but never drive the lead-time claim.
        mentions = tuple(m for m in raw if m.position in {"title", "name"})
        probed += 1
        pre = _count(mentions, youtube_first - timedelta(days=PRE_WINDOW_DAYS), youtube_first)
        baseline = _count(
            mentions,
            youtube_first - timedelta(days=BASELINE_OFFSET_DAYS + PRE_WINDOW_DAYS),
            youtube_first - timedelta(days=BASELINE_OFFSET_DAYS),
        )
        window = [
            mention
            for mention in mentions
            if youtube_first - timedelta(days=PRE_WINDOW_DAYS) <= mention.at < youtube_first
        ]
        lead = (
            (youtube_first - min(m.at for m in window)).total_seconds() / 86_400 if window else 0.0
        )
        confirmed += int(entity.confirmed)
        corroborated += int(entity.corroborated)
        if pre > baseline and window:
            bursty += 1
            leads.append(lead)
        head = min(window, key=lambda m: m.at).title[:44] if window else "-"
        flag = "**" if entity.corroborated else ("*" if entity.confirmed else " ")
        print(
            f"{flag}{term[:21]:21} {youtube_first.date()!s:>10} {pre:7.1f} {baseline:7.1f} "
            f"{lead:7.1f}  {head}"
        )
        if probed >= args.terms:
            break

    leads.sort()
    median = leads[len(leads) // 2] if leads else 0.0
    print(
        f"\nprobed={probed} entities_confirmed={confirmed} corroborated={corroborated} "
        f"with_upstream_burst={bursty} median_lead_days={median:.1f}"
    )
    print("  * named by one upstream source, ** named by two")


if __name__ == "__main__":
    main()
