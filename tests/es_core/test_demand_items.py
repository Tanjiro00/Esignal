from __future__ import annotations

import json
import math
import random
import zlib
from datetime import UTC, datetime, timedelta

from es_core.demand_items import (
    DemandComment,
    DemandItem,
    DemandPolicy,
    attach_answers,
    build_items,
)
from es_core.verification import build_request, parse_response, summarize

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def comment(
    comment_id: str,
    text: str,
    *,
    video: str = "v1",
    channel: str = "c1",
    author: str = "",
    days_ago: float = 3,
    likes: int = 0,
) -> DemandComment:
    return DemandComment(
        comment_id=comment_id,
        video_id=video,
        channel_id=channel,
        text=text,
        published_at=NOW - timedelta(days=days_ago),
        like_count=likes,
        taxonomy="explicit_question",
        author_hash=author or f"author_{comment_id}",
    )


def unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def vector(seed: int, topic: int, dimensions: int = 24) -> list[float]:
    base = random.Random(500 + topic)
    noise = random.Random(seed)
    centre = [base.gauss(0, 1) for _ in range(dimensions)]
    return unit([value + noise.gauss(0, 0.05) for value in centre])


def question_cluster(prefix: str, texts: list[str], topic: int) -> tuple[list, dict]:
    comments = [
        comment(f"{prefix}{index}", text, video=f"v{index % 3}", channel=f"c{index % 3}")
        for index, text in enumerate(texts)
    ]
    embeddings = {
        c.comment_id: vector(zlib.crc32(c.comment_id.encode()) % 9999, topic) for c in comments
    }
    return comments, embeddings


def test_item_requires_several_distinct_people_not_several_comments() -> None:
    """One person asking three times is one person."""

    texts = ["how do I export the seedance workflow?"] * 4
    comments, embeddings = question_cluster("a", texts, topic=1)
    single_author = [
        DemandComment(
            comment_id=c.comment_id,
            video_id=c.video_id,
            channel_id=c.channel_id,
            text=c.text,
            published_at=c.published_at,
            like_count=c.like_count,
            taxonomy=c.taxonomy,
            author_hash="same_person",
        )
        for c in comments
    ]

    items = build_items(single_author, embeddings, as_of=NOW, policy=DemandPolicy(window_days=30))

    assert items == ()


def test_generic_questions_do_not_become_items() -> None:
    """ "Is it free?" clusters strongly and is worth nothing as a video topic."""

    generic = ["is it free?", "is it free ?", "is this free?", "free or paid?", "is it free"]
    background = [
        comment(
            f"bg{index}",
            "is it free?",
            video=f"v{index % 4}",
            channel=f"c{index % 4}",
            days_ago=20 + index,
        )
        for index in range(40)
    ]
    comments, embeddings = question_cluster("g", generic, topic=2)
    embeddings.update({c.comment_id: vector(index, topic=2) for index, c in enumerate(background)})

    items = build_items(
        [*comments, *background],
        embeddings,
        as_of=NOW,
        policy=DemandPolicy(window_days=45),
    )

    assert all("free" not in item.subject for item in items)


def test_answer_search_ignores_the_video_the_question_was_asked_under() -> None:
    """The carrier video demonstrably failed to answer — people asked anyway."""

    item = DemandItem(
        item_id="d_test",
        question="how do I keep the character consistent?",
        comments=(comment("q1", "how do I keep the character consistent?", video="carrier"),),
        centroid=tuple(vector(1, topic=3)),
        distinct_askers=3,
        distinct_videos=2,
        distinct_channels=2,
        total_likes=0,
        first_asked_at=NOW - timedelta(days=3),
        last_asked_at=NOW - timedelta(days=1),
        mean_similarity=0.8,
        answers=(),
    )
    embeddings = {"carrier": item.centroid, "other": item.centroid}
    meta = {
        "carrier": ("the video they were watching", NOW - timedelta(days=10)),
        "other": ("consistent characters explained", NOW - timedelta(days=5)),
    }

    resolved = attach_answers([item], embeddings, meta, as_of=NOW)

    answered_ids = {answer.video_id for answer in resolved[0].answers}
    assert answered_ids == {"other"}


def test_volume_counts_people_and_reach() -> None:
    item = DemandItem(
        item_id="d",
        question="q",
        comments=(),
        centroid=(1.0, 0.0),
        distinct_askers=9,
        distinct_videos=4,
        distinct_channels=6,
        total_likes=20,
        first_asked_at=NOW,
        last_asked_at=NOW,
        mean_similarity=0.7,
        answers=(),
    )

    assert item.volume_score > 9
    assert item.age_days(NOW + timedelta(days=2)) == 2.0


# ----------------------------------------------------------------- verification


def _item_with(texts: list[str]) -> DemandItem:
    return DemandItem(
        item_id="d_v",
        question=texts[0],
        comments=tuple(comment(f"c{index}", text) for index, text in enumerate(texts)),
        centroid=(1.0, 0.0),
        distinct_askers=len(texts),
        distinct_videos=2,
        distinct_channels=2,
        total_likes=3,
        first_asked_at=NOW,
        last_asked_at=NOW,
        mean_similarity=0.8,
        answers=(),
    )


def test_verdict_is_discarded_when_the_quote_was_never_said() -> None:
    """A model that invents evidence loses its whole verdict."""

    item = _item_with(["can I upload my own character sheet?", "how about custom characters?"])
    invented = json.dumps(
        {
            "verdict": "actionable",
            "need": "Viewers ask about custom characters.",
            "evidence": ["viewers demand a full character pipeline tutorial"],
        }
    )

    result = parse_response(item, invented)

    assert not result.grounded
    assert result.rejected_reason == "ungrounded_evidence"


def test_verbatim_quote_is_accepted() -> None:
    item = _item_with(["can I upload my own character sheet?", "how about custom characters?"])
    grounded = json.dumps(
        {
            "verdict": "actionable",
            "need": "Viewers want to know whether they can import their own characters.",
            "evidence": ["can I upload my own character sheet?"],
        }
    )

    result = parse_response(item, grounded)

    assert result.grounded
    assert result.evidence == ("can I upload my own character sheet?",)


def test_malformed_and_negative_answers_are_handled() -> None:
    item = _item_with(["but can it run crysis?", "will it run doom?"])

    assert not parse_response(item, "not json at all").grounded
    assert parse_response(item, "not json at all").rejected_reason == "unparseable_response"
    assert not parse_response(
        item, json.dumps({"verdict": "not_actionable", "need": "joke"})
    ).grounded


def test_request_contains_only_stored_comments() -> None:
    item = _item_with(["how do I remove the watermark?", "any way to get rid of watermark?"])

    request = build_request(item)
    payload = json.loads(request.payload)

    assert payload["comments"] == [
        "how do I remove the watermark?",
        "any way to get rid of watermark?",
    ]
    assert payload["asked_by"] == 2


def test_summary_reports_shares() -> None:
    item = _item_with(["how do I remove the watermark?"])
    good = parse_response(
        item,
        json.dumps(
            {
                "verdict": "actionable",
                "need": "Viewers want to remove the watermark.",
                "evidence": ["how do I remove the watermark?"],
            }
        ),
    )
    bad = parse_response(item, json.dumps({"verdict": "not_actionable", "need": ""}))

    summary = summarize([good, bad])

    assert summary["total"] == 2
    assert summary["actionable"] == 1
    assert summary["actionable_share"] == 0.5
