from __future__ import annotations

import math
import random
import zlib
from datetime import UTC, datetime, timedelta

from es_core import channel_profile
from es_core.demand_items import DemandItem
from es_core.feed import FeedPolicy, build_feed, overlap, overlap_vs_chance
from es_core.types import Video

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def vector(seed: int, subject: int, dimensions: int = 64, spread: float = 0.05) -> list[float]:
    base = random.Random(900 + subject)
    noise = random.Random(seed)
    centre = [base.gauss(0, 1) for _ in range(dimensions)]
    return unit([value + noise.gauss(0, spread) for value in centre])


def channel(channel_id: str, subject: int, count: int = 8) -> tuple[list[Video], dict]:
    videos = []
    embeddings = {}
    for index in range(count):
        video = Video(
            video_id=f"{channel_id}_v{index}",
            channel_id=channel_id,
            title=f"{channel_id} upload {index}",
            published_at=NOW - timedelta(days=10 + index * 3),
            discovered_at=NOW - timedelta(days=10 + index * 3),
        )
        videos.append(video)
        embeddings[video.video_id] = vector(index, subject)
    return videos, embeddings


def related_vector(seed: int, subject: int, *, closeness: float = 0.30) -> list[float]:
    """On the channel's subject, but not a duplicate of its videos.

    A question that lands right on top of an existing upload is *covered*, which
    is a different state from *relevant*. Tests need the relevant-but-uncovered
    case, so the subject direction is blended with an independent one.

    Measured over this fixture's geometry (64 dimensions, eight uploads per
    channel), the default lands a question at 0.49 from its own channel and
    0.14 from an unrelated one: above the 0.343 relevance floor, below the
    0.614 already-covered threshold, and clearly outside a foreign subject.
    """

    subject_direction = vector(0, subject, spread=0.0)
    noise = random.Random(seed)
    independent = unit([noise.gauss(0, 1) for _ in subject_direction])
    return unit(
        [
            closeness * left + (1 - closeness) * right
            for left, right in zip(subject_direction, independent, strict=True)
        ]
    )


def item(item_id: str, subject: int, *, askers: int = 5, days_ago: float = 2) -> DemandItem:
    return DemandItem(
        item_id=item_id,
        question=f"question about subject {subject}",
        comments=(),
        centroid=tuple(related_vector(zlib.crc32(item_id.encode()) % 999, subject)),
        distinct_askers=askers,
        distinct_videos=2,
        distinct_channels=2,
        total_likes=askers,
        first_asked_at=NOW - timedelta(days=days_ago + 2),
        last_asked_at=NOW - timedelta(days=days_ago),
        mean_similarity=0.8,
        answers=(),
    )


def test_channels_on_different_subjects_get_different_feeds() -> None:
    """The product promise: relevance. Identical feeds mean nothing to sell."""

    left_videos, left_embeddings = channel("left", subject=1)
    right_videos, right_embeddings = channel("right", subject=2)
    embeddings = {**left_embeddings, **right_embeddings}
    items = [item(f"a{index}", subject=1) for index in range(6)]
    items += [item(f"b{index}", subject=2) for index in range(6)]

    left = channel_profile.build("left", left_videos, embeddings, as_of=NOW)
    right = channel_profile.build("right", right_videos, embeddings, as_of=NOW)
    assert left is not None and right is not None

    # Production configuration: the relevance floor is what keeps another
    # channel's subject out of this channel's feed.
    policy = FeedPolicy(maximum_items=6)
    left_feed = build_feed(left, items, embeddings, as_of=NOW, policy=policy)
    right_feed = build_feed(right, items, embeddings, as_of=NOW, policy=policy)

    assert left_feed and right_feed
    assert overlap(left_feed, right_feed) <= 0.30
    assert {entry.item.item_id[0] for entry in left_feed} == {"a"}
    assert {entry.item.item_id[0] for entry in right_feed} == {"b"}


def test_a_high_volume_off_subject_question_does_not_take_over_the_feed() -> None:
    """The bug this ranking was rewritten to fix.

    Multiplying raw components let volume, which ranges far wider than fit,
    decide every feed. Percentile ranks put them on one scale.
    """

    videos, embeddings = channel("mine", subject=1)
    on_subject = item("on", subject=1, askers=4)
    off_subject = item("off", subject=2, askers=400)
    embeddings.update({"x": vector(1, 1)})

    profile = channel_profile.build("mine", videos, embeddings, as_of=NOW)
    assert profile is not None
    feed = build_feed(
        profile,
        [on_subject, off_subject],
        embeddings,
        as_of=NOW,
        policy=FeedPolicy(minimum_fit=0.0),
    )

    assert feed[0].item.item_id == "on"


def test_questions_the_channel_already_answered_drop_below_the_fold() -> None:
    videos, embeddings = channel("mine", subject=1)
    covered = item("covered", subject=1)
    fresh = item("fresh", subject=1)
    # One upload sits exactly on the covered question; the other stays open.
    embeddings["mine_v0"] = list(covered.centroid)

    profile = channel_profile.build("mine", videos, embeddings, as_of=NOW)
    assert profile is not None
    feed = build_feed(
        profile, [covered, fresh], embeddings, as_of=NOW, policy=FeedPolicy(minimum_fit=0.0)
    )

    by_id = {entry.item.item_id: entry for entry in feed}
    assert by_id["covered"].covered_by_own_videos
    assert not by_id["covered"].actionable
    assert feed[0].item.item_id == "fresh"


def test_profile_needs_enough_uploads() -> None:
    videos, embeddings = channel("thin", subject=1, count=2)

    assert channel_profile.build("thin", videos, embeddings, as_of=NOW) is None


def test_fit_uses_the_nearest_upload_not_the_average() -> None:
    """A channel covering two subjects should match questions on either."""

    first, first_embeddings = channel("multi", subject=1, count=5)
    second, second_embeddings = channel("multi", subject=5, count=5)
    second = [
        Video(
            video_id=f"multi_b{index}",
            channel_id="multi",
            title=video.title,
            published_at=video.published_at,
            discovered_at=video.discovered_at,
        )
        for index, video in enumerate(second)
    ]
    embeddings = {**first_embeddings}
    embeddings.update({video.video_id: vector(index, 5) for index, video in enumerate(second)})

    profile = channel_profile.build("multi", [*first, *second], embeddings, as_of=NOW)
    assert profile is not None

    on_second_subject = item("q", subject=5)
    assert profile.question_fit(on_second_subject.centroid) > profile.fit(
        on_second_subject.centroid
    )


def test_overlap_is_normalized_by_what_chance_would_give() -> None:
    """Raw overlap percentages are not comparable across pool sizes.

    Filtering a pool raises raw overlap even when personalization improves,
    because fewer items means more collisions by chance alone. Measured on
    production data, verification took the pool from 109 to 50: raw overlap rose
    from 50% to 62% while overlap against chance fell from 2.73x to 1.95x.
    """

    videos, embeddings = channel("mine", subject=1)
    profile = channel_profile.build("mine", videos, embeddings, as_of=NOW)
    assert profile is not None
    items = [item(f"a{index}", subject=1) for index in range(4)]
    feed = build_feed(profile, items, embeddings, as_of=NOW, policy=FeedPolicy(maximum_items=4))

    # Taking the entire pool cannot be better than chance.
    assert overlap_vs_chance(feed, feed, pool_size=len(feed)) == 1.0
    # The same feed drawn from a pool ten times larger is ten times unlikelier.
    assert overlap_vs_chance(feed, feed, pool_size=len(feed) * 10) == 10.0
    assert overlap_vs_chance(feed, (), pool_size=40) == 0.0
