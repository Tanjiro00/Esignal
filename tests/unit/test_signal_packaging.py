from packages.packaging import (
    PACKAGING_VERSION,
    build_signal_packaging,
    regenerate_packaging_section,
)


def _angle() -> dict[str, object]:
    return {
        "title": "Local AI video generation without subscriptions",
        "audience_promise": "Decide whether a local workflow is viable for weekly production.",
        "unanswered_question": "Can a local workflow match cloud quality without hidden costs?",
        "differentiation": "Existing videos show setup but not a repeated production test.",
        "evidence": ["video:1", "video:2", "demand:1"],
    }


def test_packaging_has_distinct_strategies_without_full_script() -> None:
    packaging = build_signal_packaging(
        angle=_angle(),
        evidence_ids=["video:1", "video:2", "demand:1"],
    )

    titles = packaging["title_directions"]
    assert len(titles) == 10
    assert len({item["strategy"] for item in titles}) == 10
    assert len({item["text"] for item in titles}) == 10
    assert len(packaging["hook_directions"]) == 3
    assert len(packaging["thumbnail_directions"]) == 3
    assert packaging["full_script_generated"] is False
    assert packaging["version"] == PACKAGING_VERSION
    assert all("guarantee" not in item["text"].lower() for item in packaging["title_directions"])


def test_regeneration_changes_only_requested_section() -> None:
    initial = build_signal_packaging(
        angle=_angle(),
        evidence_ids=["video:1"],
    )
    regenerated = regenerate_packaging_section(
        current=initial,
        section="title_directions",
        angle=_angle(),
        evidence_ids=["video:1"],
        revision=1,
    )

    assert regenerated["title_directions"] != initial["title_directions"]
    assert regenerated["hook_directions"] == initial["hook_directions"]
    assert regenerated["proof_requirements"] == initial["proof_requirements"]
    assert regenerated["full_script_generated"] is False
